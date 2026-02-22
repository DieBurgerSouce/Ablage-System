"""SQLAlchemy models fuer das Privat-Modul (Persoenliches Dokumentenmanagement).

Extrahiert aus models.py im Rahmen der Modularisierung Phase 1.1.
"""

import uuid
from enum import Enum

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey,
    Index, Integer, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models_base import Base, CrossDBJSON


# =============================================================================
# PRIVAT-MODUL: Persoenliches Dokumentenmanagement
# =============================================================================

class PrivatSpaceType(str, Enum):
    """Typ des privaten Bereichs."""
    PERSONAL = "personal"
    SHARED = "shared"


class PrivatAccessLevel(str, Enum):
    """Zugriffsebenen für Privat-Bereiche."""
    NONE = "none"
    VIEW = "view"
    EDIT = "edit"
    MANAGE = "manage"


class PrivatDocumentType(str, Enum):
    """Dokumenttypen im Privat-Bereich."""
    # Immobilien
    PROPERTY_DEED = "property_deed"
    PURCHASE_CONTRACT = "purchase_contract"
    RENTAL_AGREEMENT = "rental_agreement"
    UTILITY_BILL = "utility_bill"
    PROPERTY_TAX = "property_tax"
    # Fahrzeuge
    VEHICLE_REGISTRATION = "vehicle_registration"
    VEHICLE_TITLE = "vehicle_title"
    INSURANCE_POLICY = "insurance_policy"
    SERVICE_RECORD = "service_record"
    FUEL_RECEIPT = "fuel_receipt"
    # Versicherungen
    INSURANCE_CONTRACT = "insurance_contract"
    INSURANCE_CLAIM = "insurance_claim"
    PENSION_STATEMENT = "pension_statement"
    # Steuern
    TAX_RETURN = "tax_return"
    TAX_ASSESSMENT = "tax_assessment"
    # Allgemein
    BANK_STATEMENT = "bank_statement"
    INVESTMENT_REPORT = "investment_report"
    LOAN_AGREEMENT = "loan_agreement"
    OTHER = "other"


class PrivatDeadlineType(str, Enum):
    """Typen von Fristen."""
    EXPIRY = "expiry"
    PAYMENT = "payment"
    RENEWAL = "renewal"
    CANCELLATION = "cancellation"
    REVIEW = "review"
    CUSTOM = "custom"


class PrivatEmergencyAccessStatus(str, Enum):
    """Status des Notfallzugriffs."""
    PENDING = "pending"
    ACTIVE = "active"
    GRANTED = "granted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class PrivatSpace(Base):
    """Privater Bereich - Container für private Dokumente."""
    __tablename__ = "privat_spaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Typ und Owner
    space_type = Column(String(20), nullable=False, default=PrivatSpaceType.PERSONAL.value)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)

    # Identifikation
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), default="Lock")
    color = Column(String(7), default="#6366F1")

    # Verschluesselung
    encryption_enabled = Column(Boolean, default=True)
    encryption_key_hash = Column(String(64), nullable=True)

    # Statistiken
    document_count = Column(Integer, default=0)
    folder_count = Column(Integer, default=0)
    total_size_bytes = Column(BigInteger, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], backref="privat_spaces")
    company = relationship("Company", foreign_keys=[company_id])
    folders = relationship("PrivatFolder", back_populates="space", cascade="all, delete-orphan")
    access_grants = relationship("PrivatSpaceAccess", back_populates="space", cascade="all, delete-orphan")
    documents = relationship("PrivatDocument", back_populates="space", cascade="all, delete-orphan")
    properties = relationship("PrivatProperty", back_populates="space", cascade="all, delete-orphan")
    vehicles = relationship("PrivatVehicle", back_populates="space", cascade="all, delete-orphan")
    insurances = relationship("PrivatInsurance", back_populates="space", cascade="all, delete-orphan")
    loans = relationship("PrivatLoan", back_populates="space", cascade="all, delete-orphan")
    investments = relationship("PrivatInvestment", back_populates="space", cascade="all, delete-orphan")
    deadlines = relationship("PrivatDeadline", back_populates="space", cascade="all, delete-orphan")
    emergency_contacts = relationship("PrivatEmergencyContact", back_populates="space", cascade="all, delete-orphan")
    # Enterprise Intelligence
    recurring_payments = relationship("PrivatRecurringPayment", back_populates="space", cascade="all, delete-orphan")
    coverage_gaps = relationship("PrivatCoverageGap", back_populates="space", cascade="all, delete-orphan")
    # Predictive Intelligence
    kpi_history = relationship("PrivatKPIHistory", back_populates="space", cascade="all, delete-orphan")
    projections = relationship("PrivatProjection", back_populates="space", cascade="all, delete-orphan")
    early_warnings = relationship("PrivatEarlyWarning", back_populates="space", cascade="all, delete-orphan")
    tasks = relationship("PrivatTask", back_populates="space", cascade="all, delete-orphan")
    # Portfolio & Financial Goals (Enterprise Feature)
    portfolio_snapshots = relationship("PortfolioSnapshot", back_populates="space", cascade="all, delete-orphan")
    financial_goals = relationship("FinancialGoal", back_populates="space", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_spaces_owner_id", "owner_id"),
        Index("ix_privat_spaces_company_id", "company_id"),
        Index("ix_privat_spaces_type", "space_type"),
        Index("ix_privat_spaces_deleted_at", "deleted_at"),
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_active(self) -> bool:
        """Returns True if space is not soft-deleted (inverse of is_deleted)."""
        return self.deleted_at is None


class PrivatSpaceAccess(Base):
    """Zugriffsberechtigung für Privat-Bereiche."""
    __tablename__ = "privat_space_access"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Zugriffsebene
    access_level = Column(String(20), nullable=False, default=PrivatAccessLevel.VIEW.value)

    # Wer hat Zugriff erteilt
    granted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Zeitliche Begrenzung
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    space = relationship("PrivatSpace", back_populates="access_grants")
    user = relationship("User", foreign_keys=[user_id], backref="privat_access_grants")
    granted_by = relationship("User", foreign_keys=[granted_by_id])

    __table_args__ = (
        Index("ix_privat_space_access_space_id", "space_id"),
        Index("ix_privat_space_access_user_id", "user_id"),
        Index("ix_privat_space_access_expires_at", "expires_at"),
    )

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        from datetime import datetime, timezone
        return self.expires_at < datetime.now(timezone.utc)


class PrivatFolder(Base):
    """Flexible Ordnerstruktur für private Dokumente."""
    __tablename__ = "privat_folders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="CASCADE"), nullable=True)

    # Ordner-Info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), default="Folder")
    color = Column(String(7), nullable=True)

    # Materialized Path
    path = Column(String(2000), nullable=False)
    level = Column(Integer, default=0)

    # Sortierung
    sort_order = Column(Integer, default=0)

    # Kategorie-Typ
    category_type = Column(String(50), nullable=True)

    # Statistiken
    document_count = Column(Integer, default=0)
    subfolder_count = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="folders")
    parent = relationship("PrivatFolder", remote_side=[id], backref="children")
    documents = relationship("PrivatDocument", back_populates="folder")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_privat_folders_space_id", "space_id"),
        Index("ix_privat_folders_parent_id", "parent_id"),
        Index("ix_privat_folders_path", "path"),
        Index("ix_privat_folders_category_type", "category_type"),
        Index("ix_privat_folders_deleted_at", "deleted_at"),
    )


class PrivatDocument(Base):
    """Privates Dokument mit optionaler zusätzlicher Verschluesselung."""
    __tablename__ = "privat_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Verknüpfung zum System-Dokument
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Dokument-Info
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    document_type = Column(String(50), default=PrivatDocumentType.OTHER.value)

    # Datei-Info
    file_path = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # Zusätzliche Verschluesselung
    extra_encrypted = Column(Boolean, default=False)
    encryption_salt = Column(String(64), nullable=True)
    encryption_hint = Column(String(255), nullable=True)

    # Fristenmanagement
    expiry_date = Column(Date, nullable=True)
    reminder_days = Column(Integer, nullable=True)
    reminder_sent = Column(Boolean, default=False)
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)

    # Metadaten
    doc_metadata = Column(CrossDBJSON, default=dict)  # 'metadata' ist SQLAlchemy reserved!
    tags = Column(CrossDBJSON, default=list)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Status - konsistent mit anderen Privat-Entitäten
    is_active = Column(Boolean, default=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="documents")
    folder = relationship("PrivatFolder", back_populates="documents")
    document = relationship("Document")
    created_by = relationship("User", foreign_keys=[created_by_id])
    deleted_by = relationship("User", foreign_keys=[deleted_by_id])
    deadlines = relationship("PrivatDeadline", back_populates="privat_document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_documents_space_id", "space_id"),
        Index("ix_privat_documents_folder_id", "folder_id"),
        Index("ix_privat_documents_document_type", "document_type"),
        Index("ix_privat_documents_expiry_date", "expiry_date"),
        Index("ix_privat_documents_deleted_at", "deleted_at"),
        Index("ix_privat_documents_is_active", "is_active"),
    )


class PrivatProperty(Base):
    """Immobilien-Stammdaten."""
    __tablename__ = "privat_properties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Stammdaten
    name = Column(String(255), nullable=False)
    property_type = Column(String(50), nullable=False)

    # Adresse
    street = Column(String(255), nullable=True)
    street_number = Column(String(20), nullable=True)
    postal_code = Column(String(10), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(2), default="DE")

    # Kaufdaten
    purchase_date = Column(Date, nullable=True)
    purchase_price = Column(Numeric(15, 2), nullable=True)
    notary_costs = Column(Numeric(10, 2), nullable=True)
    land_transfer_tax = Column(Numeric(10, 2), nullable=True)

    # Laufende Daten
    current_value = Column(Numeric(15, 2), nullable=True)
    value_date = Column(Date, nullable=True)

    # Grundbuch
    land_register_entry = Column(String(100), nullable=True)
    cadastral_district = Column(String(100), nullable=True)
    parcel_number = Column(String(50), nullable=True)

    # Flaeche
    living_area_sqm = Column(Numeric(10, 2), nullable=True)
    plot_area_sqm = Column(Numeric(10, 2), nullable=True)

    # Finanzierung
    loan_id = Column(UUID(as_uuid=True), ForeignKey("privat_loans.id", ondelete="SET NULL"), nullable=True)

    # Status
    is_rented = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # =========================================================================
    # Berechnete KPIs (Enterprise Feature)
    # =========================================================================
    calculated_yield = Column(Numeric(6, 2), nullable=True)  # Bruttomietrendite %
    calculated_net_yield = Column(Numeric(6, 2), nullable=True)  # Nettomietrendite %
    value_appreciation = Column(Numeric(15, 2), nullable=True)  # Wertzuwachs absolut
    value_appreciation_rate = Column(Numeric(6, 2), nullable=True)  # Wertzuwachs %
    total_costs_ytd = Column(Numeric(12, 2), nullable=True)  # Nebenkosten Year-to-Date
    calculated_roi = Column(Numeric(8, 2), nullable=True)  # Gesamt-ROI %
    annual_roi = Column(Numeric(6, 2), nullable=True)  # Jährlicher ROI %
    last_kpi_calculation = Column(DateTime(timezone=True), nullable=True)  # Letzte Berechnung

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="properties")
    folder = relationship("PrivatFolder")
    loan = relationship("PrivatLoan", foreign_keys=[loan_id])
    tenants = relationship("PrivatTenant", back_populates="property", cascade="all, delete-orphan")
    rental_incomes = relationship("PrivatRentalIncome", back_populates="property", cascade="all, delete-orphan")
    utility_statements = relationship("PrivatUtilityStatement", back_populates="property", cascade="all, delete-orphan")
    deadlines = relationship("PrivatDeadline", back_populates="property", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_properties_space_id", "space_id"),
        Index("ix_privat_properties_is_active", "is_active"),
        Index("ix_privat_properties_is_rented", "is_rented"),
    )


class PrivatTenant(Base):
    """Mieter einer Immobilie."""
    __tablename__ = "privat_tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey("privat_properties.id", ondelete="CASCADE"), nullable=False)

    # Mieterdaten
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)

    # Mietvertrag
    contract_start = Column(Date, nullable=False)
    contract_end = Column(Date, nullable=True)
    monthly_rent = Column(Numeric(10, 2), nullable=False)
    deposit = Column(Numeric(10, 2), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    property = relationship("PrivatProperty", back_populates="tenants")


class PrivatRentalIncome(Base):
    """Mieteinnahmen-Tracking."""
    __tablename__ = "privat_rental_incomes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey("privat_properties.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("privat_tenants.id", ondelete="SET NULL"), nullable=True)

    # Zahlung
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_type = Column(String(30), default="rent")

    # Referenz
    reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    property = relationship("PrivatProperty", back_populates="rental_incomes")
    tenant = relationship("PrivatTenant")


class PrivatUtilityStatement(Base):
    """Nebenkostenabrechnungen."""
    __tablename__ = "privat_utility_statements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey("privat_properties.id", ondelete="CASCADE"), nullable=False)

    # Abrechnungszeitraum
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Betraege
    total_costs = Column(Numeric(10, 2), nullable=False)
    prepayments = Column(Numeric(10, 2), nullable=False)
    balance = Column(Numeric(10, 2), nullable=False)

    # Details
    cost_breakdown = Column(CrossDBJSON, default=dict)

    # Dokument-Referenz
    document_id = Column(UUID(as_uuid=True), ForeignKey("privat_documents.id", ondelete="SET NULL"), nullable=True)

    # Status
    is_settled = Column(Boolean, default=False)
    settled_date = Column(Date, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    property = relationship("PrivatProperty", back_populates="utility_statements")
    document = relationship("PrivatDocument")


class PrivatVehicle(Base):
    """Fahrzeug-Stammdaten."""
    __tablename__ = "privat_vehicles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Fahrzeugdaten
    name = Column(String(255), nullable=False)
    license_plate = Column(String(20), nullable=True)
    vin = Column(String(17), nullable=True)

    # Details
    make = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    year = Column(Integer, nullable=True)
    fuel_type = Column(String(30), nullable=True)

    # Kauf/Leasing
    purchase_date = Column(Date, nullable=True)
    purchase_price = Column(Numeric(12, 2), nullable=True)
    is_leased = Column(Boolean, default=False)
    lease_end = Column(Date, nullable=True)
    monthly_rate = Column(Numeric(10, 2), nullable=True)

    # Versicherung
    insurance_company = Column(String(100), nullable=True)
    insurance_number = Column(String(50), nullable=True)
    insurance_type = Column(String(30), nullable=True)
    insurance_premium = Column(Numeric(10, 2), nullable=True)

    # Fristen
    tuev_due = Column(Date, nullable=True)
    inspection_due = Column(Date, nullable=True)

    # Kilometerstand
    current_mileage = Column(Integer, nullable=True)
    mileage_date = Column(Date, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # =========================================================================
    # Berechnete KPIs (Enterprise Feature)
    # =========================================================================
    current_estimated_value = Column(Numeric(12, 2), nullable=True)  # Geschätzter Restwert
    depreciation_monthly = Column(Numeric(10, 2), nullable=True)  # Monatliche Abschreibung
    tco_total = Column(Numeric(12, 2), nullable=True)  # Total Cost of Ownership
    tco_per_km = Column(Numeric(6, 3), nullable=True)  # Kosten pro Kilometer
    next_service_date = Column(Date, nullable=True)  # Nächster geplanter Service
    next_service_km = Column(Integer, nullable=True)  # Service bei km-Stand
    average_fuel_consumption = Column(Numeric(5, 2), nullable=True)  # Durchschnittsverbrauch l/100km
    last_kpi_calculation = Column(DateTime(timezone=True), nullable=True)  # Letzte Berechnung

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="vehicles")
    folder = relationship("PrivatFolder")
    fuel_logs = relationship("PrivatFuelLog", back_populates="vehicle", cascade="all, delete-orphan")
    deadlines = relationship("PrivatDeadline", back_populates="vehicle", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_vehicles_space_id", "space_id"),
        Index("ix_privat_vehicles_tuev_due", "tuev_due"),
        Index("ix_privat_vehicles_is_active", "is_active"),
    )


class PrivatFuelLog(Base):
    """Tankbelege/Ladungen."""
    __tablename__ = "privat_fuel_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("privat_vehicles.id", ondelete="CASCADE"), nullable=False)

    # Tankung
    date = Column(Date, nullable=False)
    mileage = Column(Integer, nullable=True)
    liters = Column(Numeric(6, 2), nullable=True)
    price_per_unit = Column(Numeric(6, 3), nullable=True)
    total_cost = Column(Numeric(8, 2), nullable=False)

    # Tankstelle
    station = Column(String(100), nullable=True)

    # Beleg
    receipt_document_id = Column(UUID(as_uuid=True), ForeignKey("privat_documents.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    vehicle = relationship("PrivatVehicle", back_populates="fuel_logs")
    receipt_document = relationship("PrivatDocument")


class PrivatInsurance(Base):
    """Versicherungspolicen."""
    __tablename__ = "privat_insurances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Police
    name = Column(String(255), nullable=False)
    insurance_type = Column(String(50), nullable=False)
    policy_number = Column(String(50), nullable=True)

    # Versicherer
    company = Column(String(100), nullable=False)
    agent_name = Column(String(100), nullable=True)
    agent_phone = Column(String(30), nullable=True)

    # Laufzeit
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_auto_renew = Column(Boolean, default=True)
    cancellation_period_months = Column(Integer, nullable=True)

    # Praemie
    premium_amount = Column(Numeric(10, 2), nullable=True)
    premium_frequency = Column(String(20), default="yearly")

    # Leistungen
    coverage_amount = Column(Numeric(15, 2), nullable=True)
    coverage_details = Column(CrossDBJSON, default=dict)
    deductible = Column(Numeric(10, 2), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # =========================================================================
    # Berechnete KPIs (Enterprise Feature)
    # =========================================================================
    coverage_gap_analysis = Column(CrossDBJSON, nullable=True)  # Deckungslücken-Analyse
    # Format: {"gaps": [{"type": "haftpflicht", "recommended": 10000000, "current": 5000000, "gap": 5000000, "severity": "high"}]}
    cancellation_deadline = Column(Date, nullable=True)  # Berechnete Kündigungsfrist
    annual_premium_total = Column(Numeric(10, 2), nullable=True)  # Jährliche Gesamtpraemie
    coverage_adequacy_score = Column(Numeric(5, 2), nullable=True)  # Deckungsadaequanz-Score 0-100
    last_kpi_calculation = Column(DateTime(timezone=True), nullable=True)  # Letzte Berechnung

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="insurances")
    folder = relationship("PrivatFolder")
    deadlines = relationship("PrivatDeadline", back_populates="insurance", cascade="all, delete-orphan")
    coverage_gaps = relationship("PrivatCoverageGap", back_populates="insurance", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_insurances_space_id", "space_id"),
        Index("ix_privat_insurances_type", "insurance_type"),
        Index("ix_privat_insurances_end_date", "end_date"),
        Index("ix_privat_insurances_is_active", "is_active"),
    )


class PrivatLoan(Base):
    """Kredite/Darlehen."""
    __tablename__ = "privat_loans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Kredit
    name = Column(String(255), nullable=False)
    loan_type = Column(String(50), nullable=False)
    loan_number = Column(String(50), nullable=True)

    # Bank
    bank_name = Column(String(100), nullable=False)

    # Konditionen
    principal_amount = Column(Numeric(15, 2), nullable=False)
    interest_rate = Column(Numeric(5, 3), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    # Tilgung
    monthly_payment = Column(Numeric(10, 2), nullable=True)
    current_balance = Column(Numeric(15, 2), nullable=True)
    balance_date = Column(Date, nullable=True)

    # Sondertilgung
    special_repayment_allowed = Column(Boolean, default=False)
    special_repayment_limit = Column(Numeric(10, 2), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # =========================================================================
    # Berechnete KPIs (Enterprise Feature)
    # =========================================================================
    amortization_schedule = Column(CrossDBJSON, nullable=True)  # Tilgungsplan
    # Format: [{"date": "2024-01", "payment": 1000, "principal": 300, "interest": 700, "balance": 99000}, ...]
    projected_payoff_date = Column(Date, nullable=True)  # Voraussichtliches Rückzahlungsdatum
    total_interest_projected = Column(Numeric(15, 2), nullable=True)  # Erwartete Gesamtzinsen
    interest_saved_with_extra = Column(Numeric(12, 2), nullable=True)  # Ersparnis bei Sondertilgung
    effective_annual_rate = Column(Numeric(5, 3), nullable=True)  # Effektiver Jahreszins
    remaining_term_months = Column(Integer, nullable=True)  # Verbleibende Laufzeit in Monaten
    last_kpi_calculation = Column(DateTime(timezone=True), nullable=True)  # Letzte Berechnung

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    space = relationship("PrivatSpace", back_populates="loans")
    folder = relationship("PrivatFolder")
    properties = relationship("PrivatProperty", back_populates="loan", foreign_keys="PrivatProperty.loan_id")
    deadlines = relationship("PrivatDeadline", back_populates="loan", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_loans_space_id", "space_id"),
        Index("ix_privat_loans_type", "loan_type"),
        Index("ix_privat_loans_end_date", "end_date"),
        Index("ix_privat_loans_is_active", "is_active"),
    )


class PrivatInvestment(Base):
    """Investments/Geldanlagen."""
    __tablename__ = "privat_investments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Investment
    name = Column(String(255), nullable=False)
    investment_type = Column(String(50), nullable=False)

    # Bank/Depot
    institution = Column(String(100), nullable=True)
    account_number = Column(String(50), nullable=True)

    # Werte
    purchase_value = Column(Numeric(15, 2), nullable=True)
    purchase_date = Column(Date, nullable=True)
    current_value = Column(Numeric(15, 2), nullable=True)
    value_date = Column(Date, nullable=True)

    # Details
    isin = Column(String(12), nullable=True)
    quantity = Column(Numeric(15, 6), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    space = relationship("PrivatSpace", back_populates="investments")
    folder = relationship("PrivatFolder")

    __table_args__ = (
        Index("ix_privat_investments_space_id", "space_id"),
        Index("ix_privat_investments_type", "investment_type"),
        Index("ix_privat_investments_is_active", "is_active"),
    )


class PrivatDeadline(Base):
    """Fristen mit Erinnerungen."""
    __tablename__ = "privat_deadlines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)

    # Verknüpfungen
    document_id = Column(UUID(as_uuid=True), ForeignKey("privat_documents.id", ondelete="CASCADE"), nullable=True)
    property_id = Column(UUID(as_uuid=True), ForeignKey("privat_properties.id", ondelete="CASCADE"), nullable=True)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("privat_vehicles.id", ondelete="CASCADE"), nullable=True)
    insurance_id = Column(UUID(as_uuid=True), ForeignKey("privat_insurances.id", ondelete="CASCADE"), nullable=True)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("privat_loans.id", ondelete="CASCADE"), nullable=True)

    # Frist
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    deadline_type = Column(String(30), default=PrivatDeadlineType.CUSTOM.value)
    due_date = Column(Date, nullable=False)

    # Erinnerungen
    reminder_days = Column(CrossDBJSON, default=[30, 7, 1])
    reminders_sent = Column(CrossDBJSON, default=list)

    # Wiederholung
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(String(50), nullable=True)
    next_occurrence = Column(Date, nullable=True)

    # Status
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    # iCal
    ical_uid = Column(String(100), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="deadlines")
    privat_document = relationship("PrivatDocument", back_populates="deadlines")
    property = relationship("PrivatProperty", back_populates="deadlines")
    vehicle = relationship("PrivatVehicle", back_populates="deadlines")
    insurance = relationship("PrivatInsurance", back_populates="deadlines")
    loan = relationship("PrivatLoan", back_populates="deadlines")
    created_by = relationship("User", foreign_keys=[created_by_id])
    notifications = relationship("PrivatDeadlineNotification", back_populates="deadline", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_deadlines_space_id", "space_id"),
        Index("ix_privat_deadlines_due_date", "due_date"),
        Index("ix_privat_deadlines_is_active", "is_active"),
        Index("ix_privat_deadlines_is_completed", "is_completed"),
    )


class PrivatDeadlineNotification(Base):
    """Gesendete Frist-Benachrichtigungen."""
    __tablename__ = "privat_deadline_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deadline_id = Column(UUID(as_uuid=True), ForeignKey("privat_deadlines.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Benachrichtigung
    days_before = Column(Integer, nullable=False)
    notification_type = Column(String(30), default="email")

    # Status
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered = Column(Boolean, default=False)
    read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    deadline = relationship("PrivatDeadline", back_populates="notifications")
    user = relationship("User")

    __table_args__ = (
        Index("ix_privat_deadline_notifications_deadline_id", "deadline_id"),
        Index("ix_privat_deadline_notifications_user_id", "user_id"),
        Index("ix_privat_deadline_notifications_sent_at", "sent_at"),
    )


class PrivatEmergencyContact(Base):
    """Vertrauenspersonen für Notfallzugriff/Vererbung."""
    __tablename__ = "privat_emergency_contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)

    # Vertrauensperson
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(30), nullable=True)
    contact_relationship = Column(String(50), nullable=True)  # 'relationship' ist SQLAlchemy reserved!

    # Zugriffskonfiguration
    access_level = Column(String(20), default=PrivatAccessLevel.VIEW.value)
    access_folders = Column(CrossDBJSON, default=list)

    # Aktivierung
    activation_delay_days = Column(Integer, default=30)
    requires_verification = Column(Boolean, default=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Token
    activation_token_hash = Column(String(64), nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    space = relationship("PrivatSpace", back_populates="emergency_contacts")
    access_requests = relationship("PrivatEmergencyAccessRequest", back_populates="contact", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_emergency_contacts_space_id", "space_id"),
        Index("ix_privat_emergency_contacts_email", "email"),
        Index("ix_privat_emergency_contacts_is_active", "is_active"),
    )


class PrivatEmergencyAccessRequest(Base):
    """Anfrage auf Notfallzugriff."""
    __tablename__ = "privat_emergency_access_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("privat_emergency_contacts.id", ondelete="CASCADE"), nullable=False)

    # Status
    status = Column(String(20), default=PrivatEmergencyAccessStatus.PENDING.value)

    # Zeitplanung
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    activation_scheduled_for = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Begruendung
    reason = Column(Text, nullable=True)

    # Verifizierung
    verification_code = Column(String(20), nullable=True)
    verification_document_id = Column(UUID(as_uuid=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Widerruf
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoke_reason = Column(Text, nullable=True)

    # IP/Geraet
    request_ip = Column(String(45), nullable=True)
    request_user_agent = Column(String(500), nullable=True)

    # Relationships
    contact = relationship("PrivatEmergencyContact", back_populates="access_requests")
    revoked_by = relationship("User")

    __table_args__ = (
        Index("ix_privat_emergency_access_requests_contact_id", "contact_id"),
        Index("ix_privat_emergency_access_requests_status", "status"),
        Index("ix_privat_emergency_access_requests_activation", "activation_scheduled_for"),
    )
